package audit.enforcement.action.deny.policy_0680

# Auto-generated policy 680 (Rego v1 syntax)
# Package: audit.enforcement.action.deny

# Metadata
metadata := {
    "policy_id": "0680",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0680_allowed if {
    input.user.role == "admin"
}
policy_0680_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0680_allowed if {
    input.user.active
    input.resource.public
}
