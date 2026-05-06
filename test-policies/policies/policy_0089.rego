package compliance.authorization.action.validate.helpers.policy_0089

# Auto-generated policy 89 (Rego v1 syntax)
# Package: compliance.authorization.action.validate.helpers

# Metadata
metadata := {
    "policy_id": "0089",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0089_allowed if {
    input.user.active
    input.resource.public
}
policy_0089_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0089_allowed = false
policy_0089_allowed if {
    input.user.role == "admin"
}
