# How to contribute

Thanks for wanting to improve OpenFinance. First, read [AGENTS.md](AGENTS.md): it gathers the repository's architecture, domain, security and style rules, and applies equally to people and agents.

## License

OpenFinance is distributed under [AGPL-3.0-or-later](LICENSE) ([ADR-0008](docs/adr/0008-licencia-agpl.md)). By contributing, you agree that your contribution is published under that same license. There is no CLA or assignment of rights, and files carry no license headers.

## Sign your commits (DCO)

Every commit must carry a `Signed-off-by` line with your real name and email:

```
Signed-off-by: First Last <you@email.example>
```

Git adds it for you with `-s`:

```bash
git commit -s -m "feat: …"
```

If you forgot to sign the last commit: `git commit --amend -s --no-edit`. For several commits on your branch: `git rebase --signoff main`.

With that line you certify the Developer Certificate of Origin 1.1, whose original text (<https://developercertificate.org/>) is reproduced unchanged:

```
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.


Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

## Before opening a pull request

- Reference the ticket (`OF-xxx`) from [docs/product/roadmap.md](docs/product/roadmap.md) and update its status.
- Commits follow [Conventional Commits](https://www.conventionalcommits.org/) and are signed (`-s`).
- `make check` passes. If you change the API, run `make openapi`.
- If you add a dependency, `make licenses CHECK=1` must keep passing. If its license is not on the allowed list, explain why it is compatible and update [docs/legal/dependencias.md](docs/legal/dependencias.md).
- Do not include real data: no bank statements and no secrets.
