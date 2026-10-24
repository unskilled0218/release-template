# goal

## command

- Update docs and relevant like below. so other proejcts that use this project as reference can follow.
- Suggest anything about below `Release process`

## Release process

- display log. so user can see what's going on
- if something failed, give user an instruction to fix

1. check arm64 build compability
  - if not run `docker run --privileged --rm tonistiigi/binfmt --install amd64,arm64 && docker buildx inspect --bootstrap`
2. check server connection?
3. check prerequisties are installed
4. build images
5. push

# goal

Update docs and relevant files to make the release process followable by other projects using this as a reference, including logging/clear failure instructions and any reasonable suggestions about the listed release process.
