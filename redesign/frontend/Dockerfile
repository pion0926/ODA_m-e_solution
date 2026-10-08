FROM nginx:stable-alpine
COPY redesign/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend/index.html /usr/share/nginx/html/index.html
COPY assets /usr/share/nginx/html/assets
RUN for module in app-controller.js app-shell.js app-styles.css assistant-avatar.png report-section-flow.js report-section-preview.js report-section-preview.css service-admin-ui.js service-scope.js service-auth.js service-intake.js foundation-upload.js project-ai-ui.js project-ai-ui.css dac-scoring-ui.js service-job-tray.js service-review.js service-pdm-refresh.js performance-analysis-review.js performance-analysis-review.css dac-analysis-review.js; do test -s /usr/share/nginx/html/assets/$module || exit 1; done
RUN sed -i -E 's@pid[[:space:]]+[^;]+;@pid /tmp/nginx.pid;@' /etc/nginx/nginx.conf && chown -R nginx:nginx /var/cache/nginx
USER nginx
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 CMD wget -qO- http://127.0.0.1:8080/healthz >/dev/null || exit 1
