package security.enforcement.action.deny.policy_0762

# Auto-generated policy 762 (Rego v1 syntax)
# Package: security.enforcement.action.deny

# Metadata
metadata := {
    "policy_id": "0762",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0762_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0762_allowed = false
