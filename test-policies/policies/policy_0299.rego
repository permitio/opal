package security.validation.user.check.helpers.policy_0299

# Auto-generated policy 299 (Rego v1 syntax)
# Package: security.validation.user.check.helpers

# Metadata
metadata := {
    "policy_id": "0299",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0299_allowed if {
    input.user.role == "admin"
}
policy_0299_allowed if {
    data.policies.security.enabled
}
default policy_0299_allowed = false
policy_0299_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
