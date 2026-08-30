FROM alpine:3.22

ARG POCKETBASE_VERSION=0.40.1
ARG TARGETARCH=amd64

RUN apk add --no-cache ca-certificates unzip wget \
    && case "${TARGETARCH}" in \
         amd64) PB_ARCH="amd64" ;; \
         arm64) PB_ARCH="arm64" ;; \
         *) echo "unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
       esac \
    && wget -q "https://github.com/pocketbase/pocketbase/releases/download/v${POCKETBASE_VERSION}/pocketbase_${POCKETBASE_VERSION}_linux_${PB_ARCH}.zip" -O /tmp/pb.zip \
    && unzip /tmp/pb.zip -d /pb \
    && rm /tmp/pb.zip \
    && addgroup -S pocketbase \
    && adduser -S -G pocketbase -h /pb pocketbase \
    && mkdir -p /pb/pb_data /pb/pb_migrations \
    && chown -R pocketbase:pocketbase /pb

USER pocketbase
WORKDIR /pb

EXPOSE 8090

ENTRYPOINT ["/pb/pocketbase"]
CMD ["serve", "--http=0.0.0.0:8090", "--dir=/pb/pb_data"]
