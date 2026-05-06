package security.authentication.context.deny.policy_0909

# Auto-generated policy 909 (Rego v1 syntax)
# Package: security.authentication.context.deny

# Metadata
metadata := {
    "policy_id": "0909",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0909_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0909_allowed = false
policy_0909_allowed if {
    data.policies.security.enabled
}
