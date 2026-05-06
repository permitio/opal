package compliance.validation.policy.verify.data.policy_0861

# Auto-generated policy 861 (Rego v1 syntax)
# Package: compliance.validation.policy.verify.data

# Metadata
metadata := {
    "policy_id": "0861",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0861_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0861_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0861_allowed if {
    data.policies.compliance.enabled
}
policy_0861_allowed if {
    input.user.role == "admin"
}
