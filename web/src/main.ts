import { mount } from 'svelte';
import './app.css';
import { initTheme } from './theme/theme.svelte';
import App from './App.svelte';

// Apply the persisted theme before first paint to avoid a flash of the default.
initTheme();

const app = mount(App, { target: document.getElementById('app')! });

export default app;
