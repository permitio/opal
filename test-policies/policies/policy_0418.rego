package security.validation.context.deny.policy_0418

# Auto-generated policy 418 (Rego v1 syntax)
# Package: security.validation.context.deny

# Metadata
metadata := {
    "policy_id": "0418",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0418_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0418_allowed if {
    data.policies.security.enabled
}
