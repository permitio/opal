package governance.validation.policy.validate.helpers.policy_0271

# Auto-generated policy 271 (Rego v1 syntax)
# Package: governance.validation.policy.validate.helpers

# Metadata
metadata := {
    "policy_id": "0271",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0271_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0271_allowed if {
    input.user.role == "admin"
}
policy_0271_allowed if {
    data.policies.governance.enabled
}
policy_0271_allowed if {
    input.user.active
    input.resource.public
}
