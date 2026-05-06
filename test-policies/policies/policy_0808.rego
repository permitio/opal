package compliance.authentication.user.validate.policy_0808

# Auto-generated policy 808 (Rego v1 syntax)
# Package: compliance.authentication.user.validate

# Metadata
metadata := {
    "policy_id": "0808",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0808_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0808_allowed if {
    data.policies.compliance.enabled
}
