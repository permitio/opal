package security.authorization.action.deny.policy_0565

# Auto-generated policy 565 (Rego v1 syntax)
# Package: security.authorization.action.deny

# Metadata
metadata := {
    "policy_id": "0565",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0565_allowed if {
    input.user.role == "admin"
}
policy_0565_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
