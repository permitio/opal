package compliance.authorization.context.deny.policy_0208

# Auto-generated policy 208 (Rego v1 syntax)
# Package: compliance.authorization.context.deny

# Metadata
metadata := {
    "policy_id": "0208",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0208_allowed = false
policy_0208_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0208_allowed if {
    data.policies.compliance.enabled
}
