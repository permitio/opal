package compliance.validation.policy.check.helpers.policy_0137

# Auto-generated policy 137 (Rego v1 syntax)
# Package: compliance.validation.policy.check.helpers

# Metadata
metadata := {
    "policy_id": "0137",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0137_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0137_allowed if {
    data.policies.compliance.enabled
}
policy_0137_allowed if {
    input.user.active
    input.resource.public
}
