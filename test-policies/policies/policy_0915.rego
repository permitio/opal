package compliance.validation.resource.deny.policy_0915

# Auto-generated policy 915 (Rego v1 syntax)
# Package: compliance.validation.resource.deny

# Metadata
metadata := {
    "policy_id": "0915",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0915_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0915_allowed = false
