# Platform preparation

- [Platform preparation](#platform-preparation)
  - [Install AMD64 and ARM64 emulation](#install-amd64-and-arm64-emulation)
  - [Verify runtime support](#verify-runtime-support)

## Install AMD64 and ARM64 emulation

Only an authorized host administrator may run these optional preparation commands when the selected hosts need emulation rather than native platform nodes:

```sh
docker run --privileged --rm tonistiigi/binfmt --install amd64,arm64
docker buildx inspect --bootstrap
```

The first command registers emulation handlers in the Docker daemon host's kernel. It requires privileged access and changes host configuration; it is not an ordinary application container. Verify the selected Docker context before running it. The release tool and coding agent do not run this privileged setup automatically.

The builder's advertised platforms should include `linux/amd64` and `linux/arm64`. If builder nodes or runtime daemons use different hosts, prepare each host that needs emulation, or use native nodes for the required architecture. Registering handlers on one host does not configure every remote builder or daemon. Recheck support after host restarts or environment changes.

## Verify runtime support

Builder advertising alone does not prove that containers can execute. On the Docker context used for runtime verification, run:

```sh
docker run --rm --platform linux/amd64 ubuntu:24.04 echo "Hello World"
docker run --rm --platform linux/arm64 ubuntu:24.04 echo "Hello World"
```

Both commands must exit successfully and print `Hello World`. They may pull Ubuntu images and require separate approval before execution. These checks verify architecture execution only; they do not verify this project's image, registry publication, digest promotion, or deletion safety. Use [image usage](image-usage.md) for separately approved checks of the published image, and retain the [verification limits](verification.md).
