package compliance.authentication.context.allow.helpers.policy_0090

# Auto-generated policy 90 (Rego v1 syntax)
# Package: compliance.authentication.context.allow.helpers

# Metadata
metadata := {
    "policy_id": "0090",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0090_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0090_allowed if {
    data.policies.compliance.enabled
}
