package governance.validation.policy.validate.utils.policy_0731

# Auto-generated policy 731 (Rego v1 syntax)
# Package: governance.validation.policy.validate.utils

# Metadata
metadata := {
    "policy_id": "0731",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0731_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0731_allowed if {
    input.user.active
    input.resource.public
}
policy_0731_allowed if {
    data.policies.governance.enabled
}
