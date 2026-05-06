package governance.enforcement.action.validate.policy_0743

# Auto-generated policy 743 (Rego v1 syntax)
# Package: governance.enforcement.action.validate

# Metadata
metadata := {
    "policy_id": "0743",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0743_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0743_allowed if {
    data.policies.governance.enabled
}
policy_0743_allowed if {
    input.user.active
    input.resource.public
}
default policy_0743_allowed = false
