package compliance.enforcement.resource.verify.policy_0178

# Auto-generated policy 178 (Rego v1 syntax)
# Package: compliance.enforcement.resource.verify

# Metadata
metadata := {
    "policy_id": "0178",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0178_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0178_allowed if {
    data.policies.compliance.enabled
}
policy_0178_allowed if {
    input.user.role == "admin"
}
