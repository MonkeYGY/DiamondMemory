<template>
  <div class="feedback-container">
    <iframe
      src="https://wcnc1c5oeusx.feishu.cn/share/base/form/shrcnVJ1Anmwotdi5eX9FgrbPLc"
      frameborder="0"
      class="feedback-iframe"
      sandbox="allow-scripts allow-forms allow-same-origin allow-popups"
      allowfullscreen
    ></iframe>
  </div>
</template>

<script setup lang="ts">
// 显示飞书反馈表单
</script>

<style scoped>
.feedback-container {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--color-bg);
}

.feedback-iframe {
  flex: 1;
  width: 100%;
  height: 100%;
  border: none;
}
</style>
