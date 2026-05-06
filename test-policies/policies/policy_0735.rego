package audit.enforcement.policy.deny.policy_0735

# Auto-generated policy 735 (Rego v1 syntax)
# Package: audit.enforcement.policy.deny

# Metadata
metadata := {
    "policy_id": "0735",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0735_allowed if {
    input.user.active
    input.resource.public
}
policy_0735_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
