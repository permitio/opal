package governance.validation.action.validate.utils.policy_0942

# Auto-generated policy 942 (Rego v1 syntax)
# Package: governance.validation.action.validate.utils

# Metadata
metadata := {
    "policy_id": "0942",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0942_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0942_allowed if {
    input.user.role == "admin"
}
policy_0942_allowed if {
    data.policies.governance.enabled
}
policy_0942_allowed if {
    input.user.active
    input.resource.public
}
