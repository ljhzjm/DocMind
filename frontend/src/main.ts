// Vue 概念：createApp 创建根应用，use 注册 Pinia、Router 和 UI 插件。
// Vue 概念：Pinia 在所有组件之间共享状态，Router 负责页面导航。
// Vue 概念：挂载到 #app 后，Vue 接管 index.html 中的应用容器。

import { createPinia } from 'pinia'
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'

import App from './App.vue'
import { router } from './router'
import './style.css'

createApp(App).use(createPinia()).use(router).use(ElementPlus).mount('#app')
