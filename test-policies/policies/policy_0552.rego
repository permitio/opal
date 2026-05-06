package governance.validation.user.allow.policy_0552

# Auto-generated policy 552 (Rego v1 syntax)
# Package: governance.validation.user.allow

# Metadata
metadata := {
    "policy_id": "0552",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0552_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0552_allowed if {
    input.user.role == "admin"
}
policy_0552_allowed if {
    input.user.active
    input.resource.public
}
