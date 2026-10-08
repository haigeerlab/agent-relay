# Todo: ci-macos

- [x] Task 1: doctor names its toolchain (D81) — `test_doctor.py` `test_toolchain_names_python_and_node` (with a runtime and without one: ok, exact detail `python <sys.executable> (<version>); node /opt/node/bin/node (v24.18.0, from PATH)`; failing selection: warn with the selector's detail and the Node 22.5.0 hint): red (unknown `node_selector`), green after `_toolchain` and the `node_selector` parameter (also used by the probe). The healthy-setup test then went warn because its fake node is the Python executable; the fixture now injects the node selection as it already injects the probe, so doctor tests do not depend on the machine's Node (needed on CI). `test_doctor` 19 ok; the other doctor users (`test_mailbox_read_only`, `test_node_select`, `test_runtime_uninstall`, skill entry tests) OK. collaboration-ops skill mentions `toolchain`; CHANGELOG entry
- [ ] Task 2: the workflow (D80, D80a, D82)
- [ ] Checkpoint (report): local validation on Python 3.9, 3.10, 3.14 + bridge `npm run check`
- [ ] Task 3: first CI run on GitHub (push + draft PR)
- [ ] Checkpoint (gate): module review
