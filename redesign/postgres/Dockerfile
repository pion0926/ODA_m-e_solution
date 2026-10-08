FROM postgres:17-alpine
COPY redesign/postgres/001-create-app-role.sh /docker-entrypoint-initdb.d/001-create-app-role.sh
RUN sed -i 's/\r$//' /docker-entrypoint-initdb.d/001-create-app-role.sh \
    && chmod 0555 /docker-entrypoint-initdb.d/001-create-app-role.sh \
    && sh -n /docker-entrypoint-initdb.d/001-create-app-role.sh
