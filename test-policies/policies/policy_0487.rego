package audit.validation.user.check.policy_0487

# Auto-generated policy 487 (Rego v1 syntax)
# Package: audit.validation.user.check

# Metadata
metadata := {
    "policy_id": "0487",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0487_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0487_allowed if {
    input.user.active
    input.resource.public
}
policy_0487_allowed if {
    input.user.role == "admin"
}
