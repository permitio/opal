package audit.authentication.policy.deny.core.policy_0650

# Auto-generated policy 650 (Rego v1 syntax)
# Package: audit.authentication.policy.deny.core

# Metadata
metadata := {
    "policy_id": "0650",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0650_allowed if {
    data.policies.audit.enabled
}
default policy_0650_allowed = false
