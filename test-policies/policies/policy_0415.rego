package governance.enforcement.policy.validate.policy_0415

# Auto-generated policy 415 (Rego v1 syntax)
# Package: governance.enforcement.policy.validate

# Metadata
metadata := {
    "policy_id": "0415",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0415_allowed if {
    data.policies.governance.enabled
}
policy_0415_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0415_allowed = false
policy_0415_allowed if {
    input.user.active
    input.resource.public
}
