import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { setupGlobalErrorHandler } from './utils/error-handler'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)

setupGlobalErrorHandler(app)

app.mount('#app')
