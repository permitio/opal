package compliance.authorization.context.allow.core.policy_0672

# Auto-generated policy 672 (Rego v1 syntax)
# Package: compliance.authorization.context.allow.core

# Metadata
metadata := {
    "policy_id": "0672",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0672_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0672_allowed if {
    data.policies.compliance.enabled
}
