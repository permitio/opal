package governance.authorization.policy.validate.policy_0224

# Auto-generated policy 224 (Rego v1 syntax)
# Package: governance.authorization.policy.validate

# Metadata
metadata := {
    "policy_id": "0224",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0224_allowed = false
policy_0224_allowed if {
    data.policies.governance.enabled
}
policy_0224_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0224_allowed if {
    input.user.active
    input.resource.public
}
