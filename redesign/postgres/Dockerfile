FROM postgres:17-alpine
COPY redesign/postgres/001-create-app-role.sh /docker-entrypoint-initdb.d/001-create-app-role.sh
RUN chmod 0555 /docker-entrypoint-initdb.d/001-create-app-role.sh
