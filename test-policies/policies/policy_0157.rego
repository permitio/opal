package governance.authorization.resource.check.core.policy_0157

# Auto-generated policy 157 (Rego v1 syntax)
# Package: governance.authorization.resource.check.core

# Metadata
metadata := {
    "policy_id": "0157",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0157_allowed if {
    input.user.active
    input.resource.public
}
policy_0157_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0157_allowed = false
