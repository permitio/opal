package compliance.validation.resource.deny.policy_0045

# Auto-generated policy 45 (Rego v1 syntax)
# Package: compliance.validation.resource.deny

# Metadata
metadata := {
    "policy_id": "0045",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0045_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0045_allowed if {
    input.user.active
    input.resource.public
}
policy_0045_allowed if {
    input.user.role == "admin"
}
