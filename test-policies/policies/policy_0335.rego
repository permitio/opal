package audit.authorization.policy.deny.logic.policy_0335

# Auto-generated policy 335 (Rego v1 syntax)
# Package: audit.authorization.policy.deny.logic

# Metadata
metadata := {
    "policy_id": "0335",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0335_allowed if {
    input.user.role == "admin"
}
policy_0335_allowed if {
    input.user.active
    input.resource.public
}
policy_0335_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
