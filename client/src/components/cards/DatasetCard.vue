<template>
  <tr>
    <td class="thumb-cell">
      <img
        @click="onImageClick"
        :src="imageUrl"
        class="dataset-thumb"
        @error="imageError = true"
      />
    </td>
    <td class="name-cell">
      <strong class="dataset-name">{{ dataset.name }}</strong>
      <p v-if="dataset.note" class="dataset-note">{{ dataset.note }}</p>
      <div
        v-show="$store.getters['user/loginEnabled']"
        class="dataset-owner"
      >
        Created by {{ dataset.owner }}
      </div>
    </td>
    <td class="progress-cell">
      <div v-if="dataset.numberImages > 0">
        {{ dataset.numberAnnotated }} of {{ dataset.numberImages }} annotated
        <div class="progress">
          <div
            class="progress-bar"
            role="progressbar"
            :style="{ width: percent + '%' }"
          ></div>
        </div>
      </div>
      <p v-else>No images</p>
    </td>
    <td class="categories-cell">
      <span
        v-for="(category, index) in listCategories"
        :key="index"
        class="badge badge-pill badge-primary category-badge"
        :style="{ 'background-color': category.color }"
      >
        {{ category.name }}
      </span>
    </td>
    <td class="actions-cell">
      <div class="dropdown">
        <i
          class="card-text fa fa-ellipsis-v fa-x icon-more"
          :id="'dropdownDataset' + dataset.id"
          data-toggle="dropdown"
          aria-haspopup="true"
          aria-expanded="false"
          aria-hidden="true"
        />
        <div
          class="dropdown-menu dropdown-menu-right"
          :aria-labelledby="'dropdownDataset' + dataset.id"
        >
          <button
            class="dropdown-item"
            data-toggle="modal"
            :data-target="'#datasetEdit' + dataset.id"
          >
            Edit
          </button>
          <button
            v-if="dataset.permissions.owner"
            class="dropdown-item"
            data-toggle="modal"
            :data-target="'#datasetShare' + dataset.id"
          >
            Share
          </button>
          <button
            class="dropdown-item"
            @click="onCocoDownloadClick"
            v-show="dataset.permissions.download"
          >
            Download COCO
          </button>
          <hr v-show="dataset.permissions.delete" />
          <button
            class="dropdown-item delete"
            v-show="dataset.permissions.delete"
            @click="onDeleteClick"
          >
            Delete
          </button>
        </div>
      </div>

    <!-- Edit Dataset -->
    <div class="modal fade" role="dialog" :id="'datasetEdit' + dataset.id">
      <div class="modal-dialog" role="document">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ dataset.name }}</h5>
            <button
              type="button"
              class="close"
              data-dismiss="modal"
              aria-label="Close"
            >
              <span aria-hidden="true">&times;</span>
            </button>
          </div>
          <div class="modal-body">
            <form>
              <div class="form-group">
                <label>Note</label>
                <textarea
                  v-model="note"
                  class="form-control"
                  rows="3"
                  placeholder="Additional note for this dataset"
                ></textarea>
              </div>

              <div class="form-group">
                <label>Default Categories</label>
                <TagsInput
                  v-model="selectedCategories"
                  element-id="changeDataset"
                  :existing-tags="categoryTags"
                  :typeahead="true"
                  :typeahead-activation-threshold="0"
                />
              </div>

              <Metadata
                :metadata="defaultMetadata"
                title="Default Annotation Metadata"
                key-name="Default Key"
                value-name="Default Value"
                ref="defaultAnnotation"
              />
            </form>
          </div>
          <div class="modal-footer">
            <button
              type="button"
              class="btn btn-success"
              @click="onSave"
              data-dismiss="modal"
            >
              Save
            </button>
            <button
              type="button"
              class="btn btn-secondary"
              data-dismiss="modal"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Share Dataset -->
    <div class="modal fade" role="dialog" :id="'datasetShare' + dataset.id">
      <div class="modal-dialog" role="document">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ dataset.name }}</h5>
            <button
              type="button"
              class="close"
              data-dismiss="modal"
              aria-label="Close"
            >
              <span aria-hidden="true">&times;</span>
            </button>
          </div>
          <div class="modal-body">
            <form>
              <div class="form-group">
                <label>Users shared with</label>
                <TagsInput
                  v-model="sharedUsers"
                  element-id="usersList"
                  :existing-tags="users"
                  :typeahead="true"
                  :typeahead-activation-threshold="0"
                  placeholder="Add usernames"
                />
              </div>
            </form>
          </div>
          <div class="modal-footer">
            <button
              type="button"
              class="btn btn-success"
              @click="onShare"
              data-dismiss="modal"
            >
              Save
            </button>
            <button
              type="button"
              class="btn btn-secondary"
              data-dismiss="modal"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
    </td>
  </tr>
</template>

<script>
import axios from "axios";
import Metadata from "@/components/Metadata";

import TagsInput from "@/components/TagsInput";

import { mapMutations } from "vuex";

export default {
  name: "DatasetCard",
  components: { Metadata, TagsInput },
  props: {
    dataset: {
      type: Object,
      required: true
    },
    categories: {
      type: Array,
      required: true
    }
  },
  data() {
    return {
      imageError: false,
      selectedCategories: [],
      note: this.dataset.note || "",
      defaultMetadata: this.dataset.default_annotation_metadata,
      noImageUrl: require("@/assets/no-image.png"),
      notFoundImageUrl: require("@/assets/404-image.png"),
      sharedUsers: []
    };
  },
  methods: {
    ...mapMutations(["addProcess", "removeProcess"]),
    onImageClick() {
      let identifier = this.dataset.id;
      this.$router.push({ name: "dataset", params: { identifier } });
    },
    onShare() {
      this.dataset.users = this.sharedUsers;
      axios
        .post("/api/dataset/" + this.dataset.id + "/share", {
          users: this.sharedUsers
        })
        .then(() => {
          this.$parent.updatePage();
        });
    },
    onCocoDownloadClick() {
      let process = "Generating COCO for " + this.dataset.name;
      this.addProcess(process);

      axios
        .get("/api/dataset/" + this.dataset.id + "/coco")
        .then(reponse => {
          let dataStr =
            "data:text/json;charset=utf-8," +
            encodeURIComponent(JSON.stringify(reponse.data));

          this.downloadURI(dataStr, this.dataset.name + ".json");
        })
        .finally(() => this.removeProcess(process));
    },
    onDeleteClick() {
      axios.delete("/api/dataset/" + this.dataset.id).then(() => {
        this.$parent.updatePage();
      });
    },
    onSave() {
      this.dataset.categories = this.selectedCategories;

      axios
        .post("/api/dataset/" + this.dataset.id, {
          categories: this.selectedCategories,
          note: this.note || "",
          default_annotation_metadata: this.$refs.defaultAnnotation.export()
        })
        .then(() => {
          this.$parent.updatePage();
        });
    },
    downloadURI(uri, exportName) {
      let link = document.createElement("a");
      link.href = uri;
      link.download = exportName;
      document.body.appendChild(link);
      link.click();
      link.remove();
    },
    createSelectedCategories() {
      let tagValues = Array.from([]);
      this.listCategories.forEach(category => {
        tagValues.push(category.name);
      });
      this.selectedCategories = tagValues;
    },
    createSelectedUsers() {
      this.sharedUsers = this.dataset.users;
    }
  },
  computed: {
    percent() {
      return 100 * (this.dataset.numberAnnotated / this.dataset.numberImages);
    },
    imageUrl() {
      if (this.imageError) {
        return this.notFoundImageUrl;
      }
      if (this.dataset.numberImages > 0) {
        return "/api/image/" + this.dataset.first_image_id + "?width=250";
      }

      return this.noImageUrl;
    },
    listCategories() {
      let list = [];
      if (!this.dataset.hasOwnProperty("categories")) return [];
      if (this.dataset.categories.length === 0) return [];

      this.dataset.categories.forEach(category => {
        let elements = this.categories.filter(
          element => element.id === category
        );

        if (elements.length === 1) {
          list.push(elements[0]);
        }
      });

      return list;
    },
    categoryTags() {
      let tags = {};
      this.categories.forEach(category => {
        tags[category.name] = category.name;
      });

      return tags;
    },
    users() {
      let users = {};
      this.$parent.users.forEach(user => {
        users[user.username] = user.username;
      });

      return users;
    }
  },
  watch: {
    "dataset.note"(value) {
      this.note = value || "";
    }
  },
  mounted() {
    this.createSelectedCategories();
    this.createSelectedUsers();
  }
};
</script>

<style scoped>
p {
  margin: 0;
  padding: 0 0 3px 0;
}

.thumb-cell {
  width: 96px;
}

.dataset-thumb {
  width: 84px;
  height: 64px;
  object-fit: cover;
  display: block;
  cursor: pointer;
  background: #dee2e6;
}

.name-cell {
  min-width: 280px;
}

.dataset-name {
  display: block;
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
  font-size: 15px;
  line-height: 1.35;
}

.dataset-note {
  margin: 4px 0 0 0;
  font-size: 12px;
  color: #4b5162;
  white-space: pre-wrap;
}

.dataset-owner {
  margin-top: 4px;
  color: #6c757d;
  font-size: 11px;
}

.category-badge {
  margin: 0 2px 4px 0;
}

.list-group-item {
  height: 21px;
  font-size: 13px;
  padding: 2px;
  background-color: #4b5162;
}
.icon-more {
  margin: 3px 0;
  padding: 4px 8px;
  color: black;
  cursor: pointer;
}

.thumb-cell,
.name-cell,
.progress-cell,
.categories-cell,
.actions-cell {
  text-align: left;
  vertical-align: top;
}

.actions-cell {
  width: 48px;
}

.progress {
  margin: 4px 0 0 0;
  height: 5px;
}

.delete {
  color: darkred;
}
</style>
