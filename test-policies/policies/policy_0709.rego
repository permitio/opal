package security.authorization.action.check.data.policy_0709

# Auto-generated policy 709 (Rego v1 syntax)
# Package: security.authorization.action.check.data

# Metadata
metadata := {
    "policy_id": "0709",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0709_allowed if {
    input.user.active
    input.resource.public
}
policy_0709_allowed if {
    input.user.role == "admin"
}
policy_0709_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
