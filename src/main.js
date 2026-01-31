import { createApp } from 'vue'
import { createPinia } from 'pinia'

import persist from 'pinia-plugin-persistedstate'
import App from './App.vue'
import router from './router'
import './assets/styles/main.scss'
import 'animate.css'
/* these are necessary styles for vue flow */
import '@vue-flow/core/dist/style.css';

/* this contains the default theme, these are optional styles */
import '@vue-flow/core/dist/theme-default.css';

import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'
import VirtualScroller from 'vue-virtual-scroller'



const app = createApp(App)

app.use(createPinia().use(persist))
app.use(router)
app.use(VirtualScroller)

app.mount('#app')
