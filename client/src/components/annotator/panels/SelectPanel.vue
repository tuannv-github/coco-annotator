<template>
  <div v-show="select.isActive">
    <PanelToggle name="Show Hover Text" v-model="select.hover.showText" />
    <p class="bbox-hint">Drag a box to move it. Drag a corner or an edge to resize it.</p>
  </div>
</template>

<script>
import PanelToggle from "@/components/PanelToggle";

export default {
  name: "SelectPanel",
  components: { PanelToggle },
  props: {
    select: {
      type: Object,
      required: true
    }
  }
};
</script>

<style scoped>
.bbox-hint {
  color: #6c757d;
  font-size: 12px;
  margin: 8px;
}
</style>
