# syntax=docker/dockerfile:1.7

##########################################################################
# Stage 1 - build BoxTech platform from source
##########################################################################
FROM maven:3.9-eclipse-temurin-25 AS build

WORKDIR /src

# Keep memory usage controlled.
ENV MAVEN_OPTS="-Xmx1536m" \
    NODE_OPTIONS="--max_old_space_size=2048"

COPY . .

RUN --mount=type=cache,target=/root/.m2 \
    --mount=type=cache,target=/usr/local/share/.cache/yarn \
    mvn -B -ntp clean install \
    -pl application -am \
    -DskipTests \
    -Dlicense.skip=true \
    -Dmaven.gitcommitid.skip=true \
    -Dpkg.skip.deb=true \
    -Dpkg.skip.rpm=true \
    -Dpkg.skip.zip=true \
    -Dpkg.package.phase=none \
    && cp application/target/thingsboard-*-boot.jar /boxtech.jar \
    && ls -lh /boxtech.jar

##########################################################################
# Stage 2 - runtime
##########################################################################
FROM eclipse-temurin:25-jre AS runtime

LABEL org.opencontainers.image.title="BoxTech IoT Platform" \
      org.opencontainers.image.description="Fleet telemetry, GPS tracking and real-time alerting. Built on ThingsBoard CE (Apache-2.0)." \
      org.opencontainers.image.licenses="Apache-2.0"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libharfbuzz0b \
       fontconfig \
       fonts-dejavu-core \
       curl \
    && rm -rf /var/lib/apt/lists/*

ENV BOXTECH_HOME=/usr/share/boxtech \
    BOXTECH_DATA=/data \
    JAVA_OPTS="-Xms512m -Xmx1536m"

RUN useradd \
        --system \
        --create-home \
        --home-dir ${BOXTECH_HOME} \
        --shell /usr/sbin/nologin \
        boxtech \
    && mkdir -p \
        ${BOXTECH_HOME}/bin \
        ${BOXTECH_DATA} \
        /var/log/boxtech

COPY --from=build /boxtech.jar ${BOXTECH_HOME}/bin/boxtech.jar
COPY deploy/platform/entrypoint.sh /usr/local/bin/boxtech-entrypoint.sh

RUN chmod +x /usr/local/bin/boxtech-entrypoint.sh \
    && chmod 555 ${BOXTECH_HOME}/bin/boxtech.jar \
    && chown -R boxtech:boxtech \
        ${BOXTECH_HOME} \
        ${BOXTECH_DATA} \
        /var/log/boxtech \
    && chgrp -R 0 \
        ${BOXTECH_HOME} \
        ${BOXTECH_DATA} \
        /var/log/boxtech \
    && chmod -R g=u \
        ${BOXTECH_HOME} \
        ${BOXTECH_DATA} \
        /var/log/boxtech

USER boxtech

WORKDIR ${BOXTECH_HOME}/bin

EXPOSE 8080 1883 5683/udp

HEALTHCHECK \
    --interval=15s \
    --timeout=5s \
    --start-period=180s \
    --retries=20 \
    CMD curl -fsS http://localhost:8080/login > /dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/boxtech-entrypoint.sh"]
