package governance.authentication.action.allow.utils.policy_0174

# Auto-generated policy 174 (Rego v1 syntax)
# Package: governance.authentication.action.allow.utils

# Metadata
metadata := {
    "policy_id": "0174",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0174_allowed if {
    data.policies.governance.enabled
}
policy_0174_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0174_allowed = false
