package risk.authorization.action.check.utils.policy_0901

# Auto-generated policy 901 (Rego v1 syntax)
# Package: risk.authorization.action.check.utils

# Metadata
metadata := {
    "policy_id": "0901",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0901_allowed = false
policy_0901_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0901_allowed if {
    data.policies.risk.enabled
}
