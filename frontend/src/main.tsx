import React from 'react';
import ReactDOM from 'react-dom/client';
import '@fontsource/wix-madefor-display/400.css';
import '@fontsource/wix-madefor-display/500.css';
import '@fontsource/wix-madefor-display/600.css';
import '@fontsource/wix-madefor-text/400.css';
import '@fontsource/wix-madefor-text/500.css';
import '@fontsource/wix-madefor-text/600.css';
import {
  BarElement, CategoryScale, Chart as ChartJS, Filler, Legend, LinearScale, LineElement, PointElement, Tooltip,
} from 'chart.js';
import zoomPlugin from 'chartjs-plugin-zoom';
import App from './App';
import './index.css';

ChartJS.register(LinearScale, CategoryScale, PointElement, LineElement, BarElement, Tooltip, Legend, Filler, zoomPlugin);
ChartJS.defaults.font.family = '"Wix Madefor Text", sans-serif';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
