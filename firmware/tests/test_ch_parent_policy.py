import pathlib


POLICY = pathlib.Path("firmware/ch/include/ChParentPolicy.h")
RUNTIME = pathlib.Path("firmware/ch/src/ChStarMeshRuntimeMain.cpp")


def test_ch_parent_policy_role_ranges_are_compile_time_guarded():
    policy = POLICY.read_text(encoding="utf-8")

    assert "isProvisionableChId(id)" in policy
    assert "isProvisionableGatewayId(id)" in policy
    assert "!isCandidateRoleAllowed(0x0002, 0x0001)" in policy
    assert "isCandidateRoleAllowed(0x0010, 0x0001)" in policy


def test_ch_runtime_rejects_foreign_gateway_candidates_and_cross_root_lineage():
    runtime = RUNTIME.read_text(encoding="utf-8")

    assert "isCandidateRoleAllowed(id, ROOT_GATEWAY_ID)" in runtime
    assert "reason=foreign-gateway-or-role" in runtime
    assert "candidateLineageReachesConfiguredRoot(c)" in runtime
    assert "current->advertisedParent == ROOT_GATEWAY_ID" in runtime
    assert "upstream->depth + 1 != current->depth" in runtime


def test_ch_root_gateway_change_invalidates_cached_parent_tree():
    runtime = RUNTIME.read_text(encoding="utf-8")
    start = runtime.index("bool saveRootGateway(uint16_t newId)")
    end = runtime.index("bool isValidLoraConfig", start)
    save_root = runtime[start:end]

    assert 'prefs.remove("parentId")' in save_root
    assert 'prefs.remove("parentAlt")' in save_root

