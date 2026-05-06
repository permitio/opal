package governance.enforcement.context.deny.logic.policy_0903

# Auto-generated policy 903 (Rego v1 syntax)
# Package: governance.enforcement.context.deny.logic

# Metadata
metadata := {
    "policy_id": "0903",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0903_allowed = false
policy_0903_allowed if {
    data.policies.governance.enabled
}
policy_0903_allowed if {
    input.user.role == "admin"
}
policy_0903_allowed if {
    input.user.active
    input.resource.public
}
