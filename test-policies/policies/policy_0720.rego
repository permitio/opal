package risk.validation.user.deny.core.policy_0720

# Auto-generated policy 720 (Rego v1 syntax)
# Package: risk.validation.user.deny.core

# Metadata
metadata := {
    "policy_id": "0720",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0720_allowed = false
policy_0720_allowed if {
    data.policies.risk.enabled
}
