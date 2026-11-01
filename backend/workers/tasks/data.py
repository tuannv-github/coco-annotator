
from database import (
    fix_ids,
    ImageModel,
    CategoryModel,
    AnnotationModel,
    DatasetModel,
    TaskModel,
    ExportModel
)

# import pycocotools.mask as mask
import datetime
import numpy as np
import json
import os
import shutil
import zipfile

from celery import shared_task
from config import Config
from ..socket import create_socket
from mongoengine import Q


def _yolo_box(annotation, width, height):
    bbox = annotation.get("bbox") or []
    if len(bbox) == 4 and bbox[2] > 0 and bbox[3] > 0:
        x, y, w, h = [float(value) for value in bbox]
    else:
        bounds = []
        for polygon in annotation.get("segmentation") or []:
            if not isinstance(polygon, list) or len(polygon) < 4:
                continue
            xs = polygon[0::2]
            ys = polygon[1::2]
            bounds.append((min(xs), min(ys), max(xs), max(ys)))
        if not bounds or width <= 0 or height <= 0:
            return None
        x = min(item[0] for item in bounds)
        y = min(item[1] for item in bounds)
        w = max(item[2] for item in bounds) - x
        h = max(item[3] for item in bounds) - y
    if width <= 0 or height <= 0 or w <= 0 or h <= 0:
        return None
    cx = min(max((x + w / 2.0) / width, 0.0), 1.0)
    cy = min(max((y + h / 2.0) / height, 0.0), 1.0)
    nw = min(max(w / width, 0.0), 1.0)
    nh = min(max(h / height, 0.0), 1.0)
    if nw <= 0 or nh <= 0:
        return None
    return cx, cy, nw, nh


def _write_yolo(task, dataset, coco, directory):
    images_dir = os.path.join(directory, "images")
    labels_dir = os.path.join(directory, "labels")
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(labels_dir, exist_ok=True)

    class_index = {
        category["id"]: index for index, category in enumerate(coco["categories"])
    }
    by_image = {}
    for annotation in coco["annotations"]:
        by_image.setdefault(annotation["image_id"], []).append(annotation)

    names = []
    for index, category in enumerate(coco["categories"]):
        name = str(category.get("name", index)).replace("'", "''")
        names.append(f"  {index}: '{name}'")
    with open(os.path.join(directory, "data.yaml"), "w") as handle:
        handle.write("path: .\ntrain: images\nval: images\nnames:\n")
        handle.write("\n".join(names))
        handle.write("\n")

    for image in coco["images"]:
        file_name = image.get("file_name")
        if not file_name:
            continue
        stem = os.path.splitext(file_name)[0]
        lines = []
        for annotation in by_image.get(image.get("id"), []):
            class_id = class_index.get(annotation.get("category_id"))
            if class_id is None:
                continue
            box = _yolo_box(annotation, image.get("width") or 0, image.get("height") or 0)
            if box is None:
                continue
            lines.append(
                f"{class_id} {box[0]:.6f} {box[1]:.6f} {box[2]:.6f} {box[3]:.6f}"
            )
        with open(os.path.join(labels_dir, stem + ".txt"), "w") as handle:
            if lines:
                handle.write("\n".join(lines))
                handle.write("\n")
        destination = os.path.join(images_dir, file_name)
        source = image.get("path") or os.path.join(dataset.directory, file_name)
        if os.path.islink(destination) or not os.path.isfile(destination):
            if os.path.lexists(destination):
                os.remove(destination)
            shutil.copy2(source, destination)

    zip_path = directory + ".zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for folder, _, files in os.walk(directory):
            for name in files:
                full = os.path.join(folder, name)
                archive.write(full, os.path.relpath(full, os.path.dirname(directory)))
    task.info(f"Writing YOLO dataset to {directory}")
    return zip_path


@shared_task
def export_annotations(task_id, dataset_id, categories, with_empty_images=False, export_format="coco"):

    task = TaskModel.objects.get(id=task_id)
    dataset = DatasetModel.objects.get(id=dataset_id)

    task.update(status="PROGRESS")
    socket = create_socket()

    export_format = (export_format or "coco").lower()
    task.info(f"Beginning Export ({export_format.upper()} format)")

    db_categories = CategoryModel.objects(id__in=categories, deleted=False) \
        .only(*CategoryModel.COCO_PROPERTIES)
    db_images = ImageModel.objects(
        deleted=False, dataset_id=dataset.id).only(
        *ImageModel.COCO_PROPERTIES)
    db_annotations = AnnotationModel.objects(
        deleted=False, category_id__in=categories)

    total_items = db_categories.count()

    coco = {
        'images': [],
        'categories': [],
        'annotations': []
    }

    total_items += db_images.count()
    progress = 0

    # iterate though all categoires and upsert
    category_names = []
    for category in fix_ids(db_categories):

        if len(category.get('keypoint_labels', [])) > 0:
            category['keypoints'] = category.pop('keypoint_labels', [])
            category['skeleton'] = category.pop('keypoint_edges', [])
        else:
            if 'keypoint_edges' in category:
                del category['keypoint_edges']
            if 'keypoint_labels' in category:
                del category['keypoint_labels']

        task.info(f"Adding category: {category.get('name')}")
        coco.get('categories').append(category)
        category_names.append(category.get('name'))

        progress += 1
        task.set_progress((progress / total_items) * 100, socket=socket)

    total_annotations = db_annotations.count()
    total_images = db_images.count()
    for image in db_images:
        image = fix_ids(image)

        progress += 1
        task.set_progress((progress / total_items) * 100, socket=socket)

        annotations = db_annotations.filter(image_id=image.get('id'))\
            .only(*AnnotationModel.COCO_PROPERTIES)
        annotations = fix_ids(annotations)

        if len(annotations) == 0:
            if with_empty_images:
                coco.get('images').append(image)
            continue

        num_annotations = 0
        for annotation in annotations:

            has_keypoints = len(annotation.get('keypoints', [])) > 0
            has_segmentation = len(annotation.get('segmentation', [])) > 0

            if has_keypoints or has_segmentation:

                if not has_keypoints:
                    if 'keypoints' in annotation:
                        del annotation['keypoints']
                else:
                    arr = np.array(annotation.get('keypoints', []))
                    arr = arr[2::3]
                    annotation['num_keypoints'] = len(arr[arr > 0])

                num_annotations += 1
                coco.get('annotations').append(annotation)

        task.info(
            f"Exporting {num_annotations} annotations for image {image.get('id')}")
        coco.get('images').append(image)

    task.info(
        f"Done export {total_annotations} annotations and {total_images} images from {dataset.name}")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    directory = os.path.join(Config.EXPORT_DIRECTORY.rstrip("/"), dataset.name)
    os.makedirs(directory, exist_ok=True)

    if export_format == "yolo":
        folder = os.path.join(directory, f"yolo_{timestamp}")
        os.makedirs(folder, exist_ok=True)
        file_path = _write_yolo(task, dataset, coco, folder)
        tag = "YOLO"
    else:
        file_path = os.path.join(directory, f"coco_{timestamp}.json")
        task.info(f"Writing export to file {file_path}")
        with open(file_path, 'w') as fp:
            json.dump(coco, fp)
        tag = "COCO"

    task.info("Creating export object")
    export = ExportModel(dataset_id=dataset.id, path=file_path, tags=[
                         tag, *category_names])
    export.save()

    task.set_progress(100, socket=socket)


@shared_task
def import_annotations(task_id, dataset_id, coco_json):

    task = TaskModel.objects.get(id=task_id)
    dataset = DatasetModel.objects.get(id=dataset_id)

    task.update(status="PROGRESS")
    socket = create_socket()

    task.info("Beginning Import")

    images = ImageModel.objects(dataset_id=dataset.id)
    categories = CategoryModel.objects

    coco_images = coco_json.get('images', [])
    coco_annotations = coco_json.get('annotations', [])
    coco_categories = coco_json.get('categories', [])

    task.info(f"Importing {len(coco_categories)} categories, "
              f"{len(coco_images)} images, and "
              f"{len(coco_annotations)} annotations")

    total_items = sum([
        len(coco_categories),
        len(coco_annotations),
        len(coco_images)
    ])
    progress = 0

    task.info("===== Importing Categories =====")
    # category id mapping  ( file : database )
    categories_id = {}

    # Create any missing categories
    for category in coco_categories:

        category_name = category.get('name')
        category_id = category.get('id')
        category_model = categories.filter(name__iexact=category_name).first()

        if category_model is None:
            task.warning(
                f"{category_name} category not found (creating a new one)")

            new_category = CategoryModel(
                name=category_name,
                keypoint_edges=category.get('skeleton', []),
                keypoint_labels=category.get('keypoints', [])
            )
            new_category.save()

            category_model = new_category
            dataset.categories.append(new_category.id)

        task.info(f"{category_name} category found")
        # map category ids
        categories_id[category_id] = category_model.id

        # update progress
        progress += 1
        task.set_progress((progress / total_items) * 100, socket=socket)

    dataset.update(set__categories=dataset.categories)

    task.info("===== Loading Images =====")
    # image id mapping ( file: database )
    images_id = {}
    categories_by_image = {}

    # Find all images
    for image in coco_images:
        image_id = image.get('id')
        image_filename = image.get('file_name')

        # update progress
        progress += 1
        task.set_progress((progress / total_items) * 100, socket=socket)

        image_model = images.filter(file_name__exact=image_filename).all()

        if len(image_model) == 0:
            task.warning(f"Could not find image {image_filename}")
            continue

        if len(image_model) > 1:
            task.error(
                f"Too many images found with the same file name: {image_filename}")
            continue

        task.info(f"Image {image_filename} found")
        image_model = image_model[0]
        images_id[image_id] = image_model
        categories_by_image[image_id] = list()

    task.info("===== Import Annotations =====")
    for annotation in coco_annotations:

        image_id = annotation.get('image_id')
        category_id = annotation.get('category_id')
        segmentation = annotation.get('segmentation', [])
        keypoints = annotation.get('keypoints', [])
        # is_crowd = annotation.get('iscrowed', False)
        area = annotation.get('area', 0)
        bbox = annotation.get('bbox', [0, 0, 0, 0])
        isbbox = annotation.get('isbbox', False)

        progress += 1
        task.set_progress((progress / total_items) * 100, socket=socket)

        has_segmentation = len(segmentation) > 0
        has_keypoints = len(keypoints) > 0
        if not has_segmentation and not has_keypoints:
            task.warning(
                f"Annotation {annotation.get('id')} has no segmentation or keypoints")
            continue

        try:
            image_model = images_id[image_id]
            category_model_id = categories_id[category_id]
            image_categories = categories_by_image[image_id]
        except KeyError:
            task.warning(
                f"Could not find image assoicated with annotation {annotation.get('id')}")
            continue

        annotation_model = AnnotationModel.objects(
            image_id=image_model.id,
            category_id=category_model_id,
            segmentation=segmentation,
            keypoints=keypoints
        ).first()

        if annotation_model is None:
            task.info(f"Creating annotation data ({image_id}, {category_id})")

            annotation_model = AnnotationModel(image_id=image_model.id)
            annotation_model.category_id = category_model_id

            annotation_model.color = annotation.get('color')
            annotation_model.metadata = annotation.get('metadata', {})

            if has_segmentation:
                annotation_model.segmentation = segmentation
                annotation_model.area = area
                annotation_model.bbox = bbox

            if has_keypoints:
                annotation_model.keypoints = keypoints

            annotation_model.isbbox = isbbox
            annotation_model.save()

            image_categories.append(category_id)
        else:
            annotation_model.update(deleted=False, isbbox=isbbox)
            task.info(
                f"Annotation already exists (i:{image_id}, c:{category_id})")

    for image_id in images_id:
        image_model = images_id[image_id]
        category_ids = categories_by_image[image_id]
        all_category_ids = list(image_model.category_ids)
        all_category_ids += category_ids

        num_annotations = AnnotationModel.objects(
            Q(image_id=image_id) & Q(deleted=False) &
            (Q(area__gt=0) | Q(keypoints__size__gt=0))
        ).count()

        image_model.update(
            set__annotated=True,
            set__category_ids=list(set(all_category_ids)),
            set__num_annotations=num_annotations
        )

    task.set_progress(100, socket=socket)


__all__ = ["export_annotations", "import_annotations"]
