#pragma once

#include <cstdint>

#include "FirmwareConfig.h"

namespace pgl::ch::parent_policy {

constexpr bool isStoredChIdentityAllowed(uint16_t id) {
    return pgl::config::isProvisionableChId(id);
}

constexpr bool isRootGatewayIdentityAllowed(uint16_t id) {
    return pgl::config::isProvisionableGatewayId(id);
}

constexpr bool isCandidateRoleAllowed(uint16_t candidateId, uint16_t configuredRootGatewayId) {
    return candidateId == configuredRootGatewayId ||
           pgl::config::isProvisionableChId(candidateId);
}

constexpr bool isChParentReferenceAllowed(uint16_t advertisedParentId, uint16_t configuredRootGatewayId) {
    return advertisedParentId == configuredRootGatewayId ||
           pgl::config::isProvisionableChId(advertisedParentId);
}

static_assert(isStoredChIdentityAllowed(0x0010));
static_assert(isStoredChIdentityAllowed(0x0FFF));
static_assert(!isStoredChIdentityAllowed(0x0001));
static_assert(!isStoredChIdentityAllowed(0x1001));
static_assert(isRootGatewayIdentityAllowed(0x0001));
static_assert(isRootGatewayIdentityAllowed(0x000F));
static_assert(!isRootGatewayIdentityAllowed(0x0010));
static_assert(isCandidateRoleAllowed(0x0001, 0x0001));
static_assert(!isCandidateRoleAllowed(0x0002, 0x0001));
static_assert(isCandidateRoleAllowed(0x0010, 0x0001));

}  // namespace pgl::ch::parent_policy
