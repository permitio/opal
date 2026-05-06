package governance.enforcement.action.deny.policy_0141

# Auto-generated policy 141 (Rego v1 syntax)
# Package: governance.enforcement.action.deny

# Metadata
metadata := {
    "policy_id": "0141",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0141_allowed if {
    input.user.active
    input.resource.public
}
policy_0141_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0141_allowed = false
