FROM nginx:1.27-alpine
COPY redesign/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY 0821_OoooDaon_v1.0.html /usr/share/nginx/html/index.html
COPY assets /usr/share/nginx/html/assets
RUN for module in odaon-v1-live.js report-section-flow.js report-section-preview.js report-section-preview.css service-admin-ui.js dac-scoring-ui.js service-job-tray.js; do test -s /usr/share/nginx/html/assets/$module || exit 1; done
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 CMD wget -qO- http://127.0.0.1/healthz >/dev/null || exit 1
