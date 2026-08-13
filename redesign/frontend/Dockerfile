FROM nginx:1.27-alpine
COPY redesign/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY ["ImpactOps_대시보드_리디자인.html", "/usr/share/nginx/html/index.html"]
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 CMD wget -qO- http://127.0.0.1/healthz >/dev/null || exit 1
