package compliance.validation.user.allow.policy_0375

# Auto-generated policy 375 (Rego v1 syntax)
# Package: compliance.validation.user.allow

# Metadata
metadata := {
    "policy_id": "0375",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0375_allowed if {
    input.user.active
    input.resource.public
}
policy_0375_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0375_allowed = false
policy_0375_allowed if {
    input.user.role == "admin"
}
