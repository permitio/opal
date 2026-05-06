package governance.authorization.user.verify.helpers.policy_0176

# Auto-generated policy 176 (Rego v1 syntax)
# Package: governance.authorization.user.verify.helpers

# Metadata
metadata := {
    "policy_id": "0176",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0176_allowed if {
    input.user.role == "admin"
}
policy_0176_allowed if {
    input.user.active
    input.resource.public
}
default policy_0176_allowed = false
