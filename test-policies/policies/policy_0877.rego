package access.enforcement.user.check.policy_0877

# Auto-generated policy 877 (Rego v1 syntax)
# Package: access.enforcement.user.check

# Metadata
metadata := {
    "policy_id": "0877",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0877_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0877_allowed = false
policy_0877_allowed if {
    input.user.role == "admin"
}
